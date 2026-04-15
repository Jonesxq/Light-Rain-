import json

# 读取评估报告
with open('ragas_evaluation_report_20260411_115113.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=" * 60)
print("RAGas Evaluation Report Statistics")
print("=" * 60)
print()

total = len(data)
faithfulness_scores = []
answer_relevancy_scores = []
context_precision_scores = []
context_recall_scores = []

for item in data:
    f = item.get('faithfulness')
    ar = item.get('answer_relevancy')
    cp = item.get('context_precision')
    cr = item.get('context_recall')
    
    if f is not None:
        faithfulness_scores.append(f)
    if ar is not None:
        answer_relevancy_scores.append(ar)
    if cp is not None:
        context_precision_scores.append(cp)
    if cr is not None:
        context_recall_scores.append(cr)

print(f"Total test questions: {total}")
print()

print("=" * 60)
print("Metrics Statistics")
print("=" * 60)
print()

avg_faithfulness = sum(faithfulness_scores) / total
avg_answer_relevancy = sum(answer_relevancy_scores) / total
avg_context_precision = sum(context_precision_scores) / total
avg_context_recall = sum(context_recall_scores) / total

print(f"faithfulness: {avg_faithfulness:.4f}")
print(f"   - Range: [{min(faithfulness_scores):.4f}, {max(faithfulness_scores):.4f}]")
print(f"   - Perfect score (1.0): {faithfulness_scores.count(1.0)} / {total}")
print()

print(f"answer_relevancy: {avg_answer_relevancy:.4f}")
print(f"   - Range: [{min(answer_relevancy_scores):.4f}, {max(answer_relevancy_scores):.4f}]")
print()

print(f"context_precision: {avg_context_precision:.4f}")
print(f"   - Range: [{min(context_precision_scores):.4f}, {max(context_precision_scores):.4f}]")
print(f"   - Perfect score (1.0): {context_precision_scores.count(1.0)} / {total}")
print()

print(f"context_recall: {avg_context_recall:.4f}")
print(f"   - Range: [{min(context_recall_scores):.4f}, {max(context_recall_scores):.4f}]")
print(f"   - Perfect score (1.0): {context_recall_scores.count(1.0)} / {total}")
print()

print("=" * 60)
print("Issues Found")
print("=" * 60)
print()

# 检查低分数的问题
low_faithfulness = [item for item in data if item['faithfulness'] < 1.0]
if low_faithfulness:
    print(f"faithfulness < 1.0: {len(low_faithfulness)} questions")
    for item in low_faithfulness[:3]:
        print(f"   - Q: {item['user_input']}")
        print(f"     score: {item['faithfulness']:.4f}")
    if len(low_faithfulness) > 3:
        print(f"   ... and {len(low_faithfulness) - 3} more")
    print()

low_answer_relevancy = [item for item in data if item['answer_relevancy'] < 0.7]
if low_answer_relevancy:
    print(f"answer_relevancy < 0.7: {len(low_answer_relevancy)} questions")
    for item in low_answer_relevancy[:3]:
        print(f"   - Q: {item['user_input']}")
        print(f"     score: {item['answer_relevancy']:.4f}")
    if len(low_answer_relevancy) > 3:
        print(f"   ... and {len(low_answer_relevancy) - 3} more")
    print()

print("=" * 60)
print("Retrieved Contexts Analysis")
print("=" * 60)
print()

# 检查是否有多个 QA 对混在一个 context 中
for i, item in enumerate(data[:5]):
    print(f"Question {i+1}: {item['user_input']}")
    print(f"  Retrieved contexts: {len(item['retrieved_contexts'])}")
    for j, ctx in enumerate(item['retrieved_contexts']):
        if '---' in ctx:
            qa_count = ctx.count('---') + 1
            print(f"  Context {j+1}: Contains {qa_count} QA pairs!")
    print()

print("=" * 60)