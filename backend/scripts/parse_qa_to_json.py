"""
将 "问题：xxx\n答案：yyy\n---" 格式的纯文本 QA 数据集转换为 JSON 格式。
用法：python parse_qa_to_json.py --input qa.txt --output qa_dataset.json
"""
import argparse
import json
import re
import sys


def parse_qa_text(text: str) -> list[dict]:
    """解析 '问题：.../答案：.../---' 格式的 QA 文本"""
    records = []
    blocks = re.split(r"\n---+\n?", text.strip())
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        q_match = re.search(r"^问题：(.+)", block, re.MULTILINE)
        a_match = re.search(r"^答案：([\s\S]+)", block, re.MULTILINE)
        if not q_match or not a_match:
            continue
        question = q_match.group(1).strip()
        # 答案可能跨多行，去除首位空白
        ground_truth = a_match.group(1).strip()
        records.append({"question": question, "ground_truth": ground_truth})
    return records


def main():
    parser = argparse.ArgumentParser(description="QA 文本 → JSON 数据集转换工具")
    parser.add_argument("--input", required=True, help="输入的 QA 文本文件路径")
    parser.add_argument("--output", required=True, help="输出的 JSON 文件路径")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    records = parse_qa_text(text)
    if not records:
        print("❌ 未解析到任何 QA 数据，请检查输入文件格式。", file=sys.stderr)
        sys.exit(1)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"✅ 共解析 {len(records)} 条 QA 记录，已保存到 {args.output}")


if __name__ == "__main__":
    main()
