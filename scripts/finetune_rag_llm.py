"""
Nebula RAG Fine-Tuning Script using HuggingFace PEFT (LoRA / QLoRA) & TRL.

This script fine-tunes Qwen2.5-3B-Instruct on the Nebula RAG grounding dataset
to minimize hallucinations, enforce strict memory adherence, and maintain
the Egyptian Arabic persona.

Usage:
    python scripts/finetune_rag_llm.py [--base_model Qwen/Qwen2.5-3B-Instruct] [--epochs 3] [--output_dir models/nebula_rag_lora]
"""

import argparse
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune LLM for Nebula RAG Anti-Hallucination")
    parser.add_argument("--base_model", type=str, default="MBZUAI-Paris/Nile-Chat-3x4B-A6B", help="HuggingFace model ID")
    parser.add_argument("--train_file", type=str, default="data/rag_finetune/train_chatml.jsonl", help="Train dataset")
    parser.add_argument("--val_file", type=str, default="data/rag_finetune/val_chatml.jsonl", help="Validation dataset")
    parser.add_argument("--output_dir", type=str, default="models/nebula_nile_lora", help="Output directory for LoRA adapter")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=2, help="Per-device train batch size")
    parser.add_argument("--grad_accum", type=int, default=4, help="Gradient accumulation steps")
    parser.add_argument("--learning_rate", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--max_seq_length", type=int, default=1024, help="Max sequence length")
    parser.add_argument("--use_4bit", action="store_true", default=True, help="Use 4-bit QLoRA")
    return parser.parse_args()


def main():
    args = parse_args()
    print("=" * 70)
    print("🧠 بدء إعداد وتدريب الموديل على الالتزام بسياق RAG ومنع اللهلوسة")
    print("=" * 70)
    print(f"📦 الموديل الأساسي:      {args.base_model}")
    print(f"📄 بيانات التدريب:       {args.train_file}")
    print(f"📁 مجلد حفظ LoRA:        {args.output_dir}")
    print(f"⚙️  عدد الدورات (Epochs): {args.epochs}")
    print(f"⚡ 4-bit QLoRA:          {args.use_4bit}")
    print("=" * 70)

    try:
        import torch
        from datasets import load_dataset
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainingArguments,
        )
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from trl import SFTTrainer
    except ImportError as e:
        print(f"\n❌ يلزم تثبيت حزم التدريب:")
        print("   pip install torch transformers datasets trl peft bitsandbytes accelerate")
        print(f"   تفاصيل الخطأ: {e}\n")
        print("💡 ملاحظة هامة:")
        print("   إذا كنت على جهاز بدون كارت شاشة NVIDIA خارجي، يمكنك استخدام")
        print("   دفتر Google Colab المرفق في notebooks/Nebula_RAG_FineTuning.ipynb")
        print("   لإتمام التدريب مجاناً على كارت T4 في 10 دقائق فقط!")
        return

    # Check CUDA availability
    device_map = "auto" if torch.cuda.is_available() else None
    if not torch.cuda.is_available():
        print("⚠️ تنبيه: لا يتوفر كارت شاشة CUDA حالياً على هذا النظام.")
        print("   التدريب على المعالج (CPU) يستغرق وقتاً طويلاً جداً.")
        print("   يُنصح بتشغيل هذا السكريبت على كارت شاشة GPU أو عبر Google Colab.")

    # 1. Load Tokenizer
    print("\n[1/5] ⏳ تحميل الـ Tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 2. BitsAndBytes Config for QLoRA
    bnb_config = None
    if args.use_4bit and torch.cuda.is_available():
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

    # 3. Load Base Model
    print("\n[2/5] ⏳ تحميل الموديل الأساسي...")
    model_kwargs = {
        "trust_remote_code": True,
        "device_map": device_map,
    }
    if bnb_config:
        model_kwargs["quantization_config"] = bnb_config
    elif torch.cuda.is_available():
        model_kwargs["torch_dtype"] = torch.float16

    model = AutoModelForCausalLM.from_pretrained(args.base_model, **model_kwargs)

    if args.use_4bit and torch.cuda.is_available():
        model = prepare_model_for_kbit_training(model)

    # 4. LoRA Configuration
    print("\n[3/5] ⏳ إعداد طبقات LoRA للتدريب الفعال...")
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # 5. Load Dataset
    print("\n[4/5] ⏳ تجهيز بيانات RAG...")
    dataset = load_dataset(
        "json",
        data_files={"train": args.train_file, "val": args.val_file},
    )

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        logging_steps=5,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        fp16=torch.cuda.is_available(),
        optim="paged_adamw_8bit" if torch.cuda.is_available() else "adamw_torch",
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset["train"],
        eval_dataset=dataset["val"],
        peft_config=peft_config,
        dataset_text_field="messages",
        max_seq_length=args.max_seq_length,
        tokenizer=tokenizer,
        args=training_args,
    )

    print("\n[5/5] 🔥 جاري بدء التدريب الآن...")
    trainer.train()

    print(f"\n💾 جاري حفظ الـ LoRA Adapter في: {args.output_dir}")
    trainer.model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    print("\n" + "=" * 70)
    print("🎉 تم اكتمال تدريب الموديل بنجاح تام!")
    print("=" * 70)
    print("الخطوات التالية لتشغيل النموذج على Ollama:")
    print("1. دمج أوزان LoRA مع الموديل الأساسي:")
    print(f"   python scripts/merge_lora.py --base {args.base_model} --lora {args.output_dir} --out models/nebula-rag-merged")
    print("2. تحويله إلى GGUF:")
    print("   python llama.cpp/convert_hf_to_gguf.py models/nebula-rag-merged --outfile models/nebula-rag.gguf")
    print("3. إضافته في Ollama:")
    print("   ollama create nebula-rag -f Modelfile.nebula-rag")
    print("=" * 70)


if __name__ == "__main__":
    main()
