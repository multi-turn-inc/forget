#!/usr/bin/env python3
"""쌍둥이 v0 — voice-SFT (becoming-junghun.md P1의 '말' 기관).

(선행 문맥 → 정훈 실발화) 1,525쌍. run1 3대 병의 처방 전부 적용:
- EOS/pad 분리 (반복붕괴 1순위 범인 — pad=<|endoftext|>, eos=<|im_end|> 유지)
- NEFTune α=5 (소데이터 일반화, 2310.05914)
- 1에폭 · 보수 lr · 일반 지시 혼합 ~5% (no_robots — 능력 보존, 2403.08763)
- 표면 다양성은 데이터가 보장 (실대화 1,171 고유 문맥 — 문헌 임계의 12배)
홀드아웃: 시간순 마지막 60쌍 (섀도 곡선 부트스트랩용).
"""
import json
import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

BASE = "Qwen/Qwen3.5-9B"
OUT = "twin_v0_sft"

rows = [json.loads(l) for l in open("voice_pairs_v0.jsonl")]
holdout = rows[-60:]
train_rows = rows[:-60]
json.dump(holdout, open("twin_holdout.json", "w"), ensure_ascii=False)

def to_messages(r):
    return {"messages": [
        {"role": "system", "content": "너는 정훈이다. 아래는 어시스턴트의 보고다. 정훈으로서 반응하라."},
        {"role": "user", "content": r["context"]},
        {"role": "assistant", "content": r["response"]},
    ]}

data = [to_messages(r) for r in train_rows]

# 일반 지시 혼합 ~5% — 능력 보존 (실패해도 진행하되 명시)
try:
    from datasets import load_dataset
    gen_ds = load_dataset("HuggingFaceH4/no_robots", split="train[:70]")
    n_gen = 0
    for ex in gen_ds:
        msgs = ex.get("messages") or []
        if len(msgs) >= 2:
            data.append({"messages": msgs[:3]})
            n_gen += 1
    print(f"일반 혼합 {n_gen}건")
except Exception as e:
    print(f"[경고] 일반 혼합 실패 — 미포함 진행: {e}")

tok = AutoTokenizer.from_pretrained(BASE)
# EOS/pad 분리 — run1 반복붕괴의 1순위 처방
if tok.pad_token is None or tok.pad_token == tok.eos_token:
    tok.pad_token = "<|endoftext|>"

bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                         bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=bnb, device_map="auto")
lora = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, task_type="CAUSAL_LM",
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])

args = SFTConfig(output_dir=OUT, num_train_epochs=1, per_device_train_batch_size=1,
                 gradient_accumulation_steps=8, learning_rate=5e-5, lr_scheduler_type="cosine",
                 warmup_ratio=0.03, logging_steps=20, save_strategy="no", bf16=True,
                 max_length=1536, neftune_noise_alpha=5, report_to=[])
trainer = SFTTrainer(model=model, args=args, train_dataset=Dataset.from_list(data),
                     peft_config=lora, processing_class=tok)
trainer.train()
trainer.save_model(OUT)
print("=== 쌍둥이 v0 저장:", OUT, "===")

# 즉석 스모크 — 홀드아웃 3건: 쌍둥이 예측 vs 정훈 실발화
model.eval()
for r in holdout[:3]:
    text = tok.apply_chat_template(to_messages(r)["messages"][:2],
                                   add_generation_prompt=True, tokenize=False, enable_thinking=False)
    enc = tok(text, return_tensors="pt", truncation=True, max_length=1400).to(model.device)
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=120, do_sample=False, pad_token_id=tok.pad_token_id)
    pred = tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)
    print(f"\n[문맥 꼬리] …{r['context'][-100:]}")
    print(f"[쌍둥이 예측] {pred[:200]}")
    print(f"[정훈 실발화] {r['response'][:200]}")
print("\n=== 쌍둥이 스모크 완료 ===")
