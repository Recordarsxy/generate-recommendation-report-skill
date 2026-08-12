from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"
REFERENCE_SHA256 = "63CD1C855CD86ED9418C90561ABDE55E548DF45C61E04167F3869D31E8F112B8"


def file_sha256(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def value(data, key, default=""):
    result = data.get(key, default)
    return "" if result is None else str(result)


def paragraph_text(paragraph):
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))


def fail(errors, message):
    errors.append(message)


def expected_source_strings(data):
    candidate = data["candidate"]
    values = [
        value(candidate, "name"),
        value(candidate, "gender"),
        str(candidate.get("age") or ""),
        value(candidate, "marital_status"),
        value(candidate, "current_city"),
        value(candidate, "client"),
        value(candidate, "recommended_position"),
        value(data, "motivation"),
    ]
    consultant = candidate.get("consultant") or {}
    values.extend(value(consultant, key) for key in ["name", "mobile", "phone", "email"])
    values.extend(str(item) for item in data.get("recommendation_reasons", []))
    for item in data.get("education", []):
        values.extend(value(item, key) for key in ["date", "school", "degree", "major"])
    for job in data.get("work_experience", []):
        values.extend(value(job, key) for key in ["date", "company", "title", "location"])
        for item in job.get("items", []):
            if isinstance(item, str):
                values.append(item)
            else:
                values.extend([value(item, "heading"), value(item, "body")])
    for section in data.get("additional_sections", []):
        values.append(value(section, "title"))
        values.extend(str(line) for line in section.get("lines", []))
    return [item for item in values if item]


def verify(data, report, reference):
    errors = []
    if file_sha256(reference) != REFERENCE_SHA256:
        fail(errors, "reference hash mismatch")

    with ZipFile(reference) as source:
        reference_names = set(source.namelist())
        reference_parts = {name: source.read(name) for name in reference_names}
    with ZipFile(report) as output:
        output_names = set(output.namelist())
        output_parts = {name: output.read(name) for name in output_names}

    if output_names != reference_names:
        fail(errors, "DOCX package part list differs from reference")
    changed = [
        name
        for name in sorted(reference_names & output_names)
        if reference_parts[name] != output_parts[name]
    ]
    allowed_changes = {"word/document.xml", "word/header3.xml", "word/footer3.xml"}
    unexpected_changes = [name for name in changed if name not in allowed_changes]
    if unexpected_changes:
        fail(errors, f"unexpected changed package parts: {unexpected_changes}")

    document = etree.fromstring(output_parts["word/document.xml"])
    header = etree.fromstring(output_parts["word/header3.xml"])
    footer = etree.fromstring(output_parts["word/footer3.xml"])
    paragraphs = document.xpath(".//w:p", namespaces=NS)
    document_text = "".join(document.xpath(".//w:t/text()", namespaces=NS))
    header_text = "".join(header.xpath(".//w:t/text()", namespaces=NS))
    footer_text = "".join(footer.xpath(".//w:t/text()", namespaces=NS))
    all_text = document_text + header_text + footer_text

    candidate = data["candidate"]
    required = [
        f'中文姓名：{value(candidate, "name")}',
        f'性别：{value(candidate, "gender")}',
        f'婚姻状态：{value(candidate, "marital_status")}',
        f'目前工作地：{value(candidate, "current_city")}',
        f'客户：{value(candidate, "client")}',
        f'候选人：{value(candidate, "name")}',
        f'职位：{value(candidate, "recommended_position")}',
        "学历",
        "职业经验",
    ]
    age = candidate.get("age", "")
    if isinstance(age, int):
        age = f"{age}岁"
    required.append(f"年龄：{age or ''}")
    consultant = candidate.get("consultant") or {}
    required.extend(
        [
            f'顾问：{value(consultant, "name")}',
            f'手机：{value(consultant, "mobile")}',
            f'电话：{value(consultant, "phone")}',
            f'邮箱：{value(consultant, "email")}',
        ]
    )
    for text in required:
        if text not in all_text:
            fail(errors, f"missing required field: {text}")

    for text in expected_source_strings(data):
        if text not in all_text:
            fail(errors, f"missing source text: {text}")

    jobs = data.get("work_experience", [])
    if document_text.count("工作地点：") != len(jobs):
        fail(
            errors,
            f"工作地点 count mismatch: expected {len(jobs)}, found {document_text.count('工作地点：')}",
        )
    if re.search(r"(?<!工作)地点：", document_text):
        fail(errors, "found standalone 地点： label")

    expected_bullets = list(data.get("recommendation_reasons", []))
    for job in jobs:
        for item in job.get("items", []):
            if isinstance(item, str):
                expected_bullets.append(item)
            else:
                expected_bullets.append(value(item, "heading") + value(item, "body"))
    bullet_texts = [
        paragraph_text(paragraph)
        for paragraph in paragraphs
        if paragraph.find("w:pPr/w:numPr", NS) is not None
    ]
    if bullet_texts != expected_bullets:
        fail(errors, f"bullet paragraphs mismatch: expected {expected_bullets}, found {bullet_texts}")

    protected_texts = {"工作描述："}
    for job in jobs:
        tabs = "\t\t\t" if "至今" in value(job, "date") else "\t\t"
        protected_texts.update(
            {
                f'{value(job, "date")}{tabs}{value(job, "company")}',
                f'\t\t\t\t{value(job, "title")}',
                f'工作地点：{value(job, "location")}',
            }
        )
    for paragraph in paragraphs:
        text = paragraph_text(paragraph)
        if text not in protected_texts:
            continue
        ppr = paragraph.find("w:pPr", NS)
        if ppr is None:
            continue
        for property_name in ["numPr", "keepNext", "keepLines", "pageBreakBefore"]:
            if ppr.find(f"w:{property_name}", NS) is not None:
                fail(errors, f"{property_name} found on non-bullet paragraph: {text}")

    if len(document.xpath(".//w:sectPr", namespaces=NS)) != 1:
        fail(errors, "document must contain exactly one section")

    source_text = "".join(expected_source_strings(data))
    residue = [
        "王威",
        "职位：客服管理",
        "北京华御鲁采餐饮有限公司",
        "北京富国大通基金销售有限公司",
        "组建华东区域销售团队。",
        "筹建经历：具备从0到1筹建银保监会认可机构的经验",
    ]
    for text in residue:
        if text in all_text and text not in source_text:
            fail(errors, f"old-template residue found: {text}")

    if errors:
        for message in errors:
            print(f"FAIL: {message}")
        return 1
    print("PASS: approved package structure preserved")
    print("PASS: source wording and required fields are present")
    print("PASS: only recommendation and work items use real Word bullets")
    print("PASS: all location labels are 工作地点")
    print("PASS: non-bullet work headers have no pagination control properties")
    print("PASS: no unsupported old-template residue")
    return 0


def main():
    if len(sys.argv) not in [3, 4]:
        raise SystemExit("Usage: verify_report.py INPUT.json OUTPUT.docx [REFERENCE.docx]")
    input_path = Path(sys.argv[1]).resolve()
    report_path = Path(sys.argv[2]).resolve()
    reference_path = (
        Path(sys.argv[3]).resolve()
        if len(sys.argv) == 4
        else Path(__file__).resolve().parent.parent / "assets" / "reference.docx"
    )
    data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    raise SystemExit(verify(data, report_path, reference_path))


if __name__ == "__main__":
    main()
