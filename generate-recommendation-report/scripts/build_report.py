from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"
REFERENCE_SHA256 = "63CD1C855CD86ED9418C90561ABDE55E548DF45C61E04167F3869D31E8F112B8"


def fail(message):
    raise SystemExit(message)


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


def paragraph_has_num(paragraph):
    return paragraph.find("w:pPr/w:numPr", NS) is not None


def find_exact(paragraphs, text):
    for paragraph in paragraphs:
        if etree.QName(paragraph).localname == "p" and paragraph_text(paragraph) == text:
            return paragraph
    fail(f"Reference anchor missing: {text}")


def find_prefix(paragraphs, prefix):
    for paragraph in paragraphs:
        if etree.QName(paragraph).localname == "p" and paragraph_text(paragraph).startswith(prefix):
            return paragraph
    fail(f"Reference anchor missing: {prefix}")


def run_properties(paragraph):
    run = paragraph.find("w:r", NS)
    if run is None:
        return None
    rpr = run.find("w:rPr", NS)
    return deepcopy(rpr) if rpr is not None else None


def ensure_ppr(paragraph):
    ppr = paragraph.find("w:pPr", NS)
    if ppr is None:
        ppr = etree.Element(W + "pPr")
        paragraph.insert(0, ppr)
    return ppr


def remove_properties(paragraph, remove_numbering=False, remove_pagination=False):
    ppr = ensure_ppr(paragraph)
    names = []
    if remove_numbering:
        names.append("numPr")
    if remove_pagination:
        names.extend(["keepNext", "keepLines", "pageBreakBefore"])
    for name in names:
        child = ppr.find(f"w:{name}", NS)
        if child is not None:
            ppr.remove(child)
    return paragraph


def strip_visible_content(paragraph):
    for child in list(paragraph):
        if child.tag != W + "pPr":
            paragraph.remove(child)
    return paragraph


def append_text(paragraph, text, rpr=None):
    for index, segment in enumerate(str(text).split("\t")):
        if index:
            tab_run = etree.SubElement(paragraph, W + "r")
            if rpr is not None:
                tab_run.append(deepcopy(rpr))
            etree.SubElement(tab_run, W + "tab")
        if segment:
            run = etree.SubElement(paragraph, W + "r")
            if rpr is not None:
                run.append(deepcopy(rpr))
            node = etree.SubElement(run, W + "t")
            if segment.startswith(" ") or segment.endswith(" ") or "  " in segment:
                node.set(f"{{{XML_NS}}}space", "preserve")
            node.text = segment


def replace_text(paragraph, text, remove_numbering=False, remove_pagination=False):
    rpr = run_properties(paragraph)
    strip_visible_content(paragraph)
    remove_properties(
        paragraph,
        remove_numbering=remove_numbering,
        remove_pagination=remove_pagination,
    )
    append_text(paragraph, text, rpr)
    return paragraph


def clone_text(template, text, remove_numbering=False, remove_pagination=False):
    paragraph = deepcopy(template)
    return replace_text(
        paragraph,
        text,
        remove_numbering=remove_numbering,
        remove_pagination=remove_pagination,
    )


def clone_item(template, heading, body):
    paragraph = deepcopy(template)
    rpr = run_properties(paragraph)
    strip_visible_content(paragraph)
    remove_properties(paragraph, remove_pagination=True)
    if heading:
        append_text(paragraph, heading, rpr)
        break_run = etree.SubElement(paragraph, W + "r")
        if rpr is not None:
            break_run.append(deepcopy(rpr))
        etree.SubElement(break_run, W + "br")
    append_text(paragraph, body, rpr)
    return paragraph


def replace_part_text(part_bytes, replacements):
    root = etree.fromstring(part_bytes)
    seen = set()
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        current = paragraph_text(paragraph)
        if current in replacements:
            replace_text(paragraph, replacements[current])
            seen.add(current)
    missing = set(replacements) - seen
    if missing:
        fail(f"Header/footer anchors missing: {sorted(missing)}")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def validate_input(data):
    if not isinstance(data, dict):
        fail("Input JSON must be an object")
    candidate = data.get("candidate")
    if not isinstance(candidate, dict) or not value(candidate, "name"):
        fail("candidate.name is required")
    for list_name in ["recommendation_reasons", "education", "work_experience"]:
        if not isinstance(data.get(list_name, []), list):
            fail(f"{list_name} must be a list")
    for job in data.get("work_experience", []):
        for key in ["date", "company", "title", "location"]:
            if key not in job:
                fail(f"work_experience item missing {key}")
        if not isinstance(job.get("items", []), list):
            fail("work_experience.items must be a list")


def build(data, reference, output):
    validate_input(data)
    if file_sha256(reference) != REFERENCE_SHA256:
        fail("Reference DOCX hash does not match the approved template")

    with ZipFile(reference, "r") as source:
        part_order = source.infolist()
        parts = {item.filename: source.read(item.filename) for item in part_order}

    root = etree.fromstring(parts["word/document.xml"])
    body = root.find("w:body", NS)
    if body is None:
        fail("Reference document body is missing")
    children = list(body)
    if not children or etree.QName(children[-1]).localname != "sectPr":
        fail("Reference document section structure is unexpected")

    candidate = data["candidate"]
    age = candidate.get("age", "")
    if isinstance(age, int):
        age = f"{age}岁"
    replacements = {
        "中文姓名：": value(candidate, "name"),
        "性别：": value(candidate, "gender"),
        "年龄：": str(age or ""),
        "婚姻状态：": value(candidate, "marital_status"),
        "目前工作地：": value(candidate, "current_city"),
    }
    for prefix, replacement in replacements.items():
        paragraph = find_prefix(children, prefix)
        replace_text(paragraph, prefix + replacement, remove_numbering=True, remove_pagination=True)

    recommendation_heading = find_exact(children, "推荐理由")
    recommendation_index = children.index(recommendation_heading)
    reason_slots = []
    for paragraph in children[recommendation_index + 1 :]:
        if etree.QName(paragraph).localname != "p" or not paragraph_has_num(paragraph):
            break
        reason_slots.append(paragraph)
    if not reason_slots:
        fail("Reference recommendation bullet slots are missing")

    reasons = [str(item) for item in data.get("recommendation_reasons", [])]
    for index, slot in enumerate(reason_slots):
        if index < len(reasons):
            replace_text(slot, reasons[index], remove_pagination=True)
        else:
            replace_text(slot, "", remove_numbering=True, remove_pagination=True)
    if len(reasons) > len(reason_slots):
        insertion_point = reason_slots[-1]
        for reason in reasons[len(reason_slots) :]:
            extra = clone_text(reason_slots[0], reason, remove_pagination=True)
            body.insert(body.index(insertion_point) + 1, extra)
            insertion_point = extra

    children = list(body)
    motivation_heading = find_exact(children, "求职动机")
    motivation_index = children.index(motivation_heading)
    motivation_paragraph = children[motivation_index + 1]
    replace_text(
        motivation_paragraph,
        value(data, "motivation"),
        remove_numbering=True,
        remove_pagination=True,
    )

    children = list(body)
    education_heading = find_exact(children, "学历")
    experience_heading = find_exact(children, "职业经验")
    education_index = children.index(education_heading)
    experience_index = children.index(experience_heading)

    education_template = children[education_index + 1]
    education_detail_template = children[education_index + 2]
    experience_template = deepcopy(experience_heading)
    job_template = children[experience_index + 1]
    role_template = children[experience_index + 2]
    location_template = find_prefix(children[experience_index + 1 :], "工作地点：")
    label_template = find_prefix(children[experience_index + 1 :], "工作描述")
    bullet_template = None
    for paragraph in children[experience_index + 1 :]:
        style = paragraph.find("w:pPr/w:pStyle", NS)
        if paragraph_has_num(paragraph) and style is not None:
            bullet_template = paragraph
            break
    if bullet_template is None:
        fail("Reference work bullet template is missing")
    blank_template = next(
        paragraph
        for paragraph in children[experience_index + 1 :]
        if etree.QName(paragraph).localname == "p" and paragraph_text(paragraph) == ""
    )

    for child in list(body)[education_index + 1 : -1]:
        body.remove(child)

    new_paragraphs = []
    education = data.get("education", [])
    for index, item in enumerate(education):
        if index:
            new_paragraphs.append(
                clone_text(blank_template, "", remove_numbering=True, remove_pagination=True)
            )
        new_paragraphs.append(
            clone_text(
                education_template,
                f'{value(item, "date")}\t\t{value(item, "school")}',
                remove_numbering=True,
                remove_pagination=True,
            )
        )
        detail = "  ".join(
            part for part in [value(item, "degree"), value(item, "major")] if part
        )
        new_paragraphs.append(
            clone_text(
                education_detail_template,
                f"\t\t\t\t{detail}",
                remove_numbering=True,
                remove_pagination=True,
            )
        )
    new_paragraphs.extend(
        [
            clone_text(blank_template, "", remove_numbering=True, remove_pagination=True),
            clone_text(blank_template, "", remove_numbering=True, remove_pagination=True),
            clone_text(experience_template, "职业经验", remove_numbering=True, remove_pagination=True),
        ]
    )

    for job in data.get("work_experience", []):
        date = value(job, "date")
        tabs = "\t\t\t" if "至今" in date else "\t\t"
        new_paragraphs.append(
            clone_text(
                job_template,
                f'{date}{tabs}{value(job, "company")}',
                remove_numbering=True,
                remove_pagination=True,
            )
        )
        new_paragraphs.append(
            clone_text(
                role_template,
                f'\t\t\t\t{value(job, "title")}',
                remove_numbering=True,
                remove_pagination=True,
            )
        )
        new_paragraphs.append(
            clone_text(
                location_template,
                f'工作地点：{value(job, "location")}',
                remove_numbering=True,
                remove_pagination=True,
            )
        )
        new_paragraphs.append(
            clone_text(
                label_template,
                "工作描述：",
                remove_numbering=True,
                remove_pagination=True,
            )
        )
        for item in job.get("items", []):
            if isinstance(item, str):
                heading, item_body = None, item
            else:
                heading = item.get("heading")
                item_body = value(item, "body")
            new_paragraphs.append(clone_item(bullet_template, heading, item_body))
        new_paragraphs.append(
            clone_text(blank_template, "", remove_numbering=True, remove_pagination=True)
        )

    for section in data.get("additional_sections", []):
        new_paragraphs.append(
            clone_text(
                experience_template,
                value(section, "title"),
                remove_numbering=True,
                remove_pagination=True,
            )
        )
        for line in section.get("lines", []):
            new_paragraphs.append(
                clone_text(
                    education_template,
                    str(line),
                    remove_numbering=True,
                    remove_pagination=True,
                )
            )
        new_paragraphs.append(
            clone_text(blank_template, "", remove_numbering=True, remove_pagination=True)
        )

    for paragraph in new_paragraphs:
        body.insert(len(body) - 1, paragraph)

    parts["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )

    parts["word/header3.xml"] = replace_part_text(
        parts["word/header3.xml"],
        {
            "客户：": f'客户：{value(candidate, "client")}',
            "候选人：王威": f'候选人：{value(candidate, "name")}',
            "职位：客服管理": f'职位：{value(candidate, "recommended_position")}',
        },
    )
    consultant = candidate.get("consultant") or {}
    parts["word/footer3.xml"] = replace_part_text(
        parts["word/footer3.xml"],
        {
            "顾问：": f'顾问：{value(consultant, "name")}',
            "手机：": f'手机：{value(consultant, "mobile")}',
            "电话：": f'电话：{value(consultant, "phone")}',
            "邮箱：": f'邮箱：{value(consultant, "email")}',
        },
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as destination:
        for item in part_order:
            destination.writestr(item, parts[item.filename])

    print(f"output={output}")
    print(f"paragraphs_inserted={len(new_paragraphs)}")
    print(f"sha256={file_sha256(output)}")


def main():
    if len(sys.argv) not in [3, 4]:
        fail("Usage: build_report.py INPUT.json OUTPUT.docx [REFERENCE.docx]")
    input_path = Path(sys.argv[1]).resolve()
    output_path = Path(sys.argv[2]).resolve()
    reference_path = (
        Path(sys.argv[3]).resolve()
        if len(sys.argv) == 4
        else Path(__file__).resolve().parent.parent / "assets" / "reference.docx"
    )
    data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    build(data, reference_path, output_path)


if __name__ == "__main__":
    main()
