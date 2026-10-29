"""
Merge LoRA adapter weights with base HuggingFace model for GGUF / Ollama deployment.
"""

import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Merge LoRA with Base Model")
    parser.add_argument("--base", type=str, default="Qwen/Qwen2.5-3B-Instruct", help="Base model ID or path")
    parser.add_argument("--lora", type=str, default="models/nebula_rag_lora", help="Path to LoRA adapter")
    parser.add_argument("--out", type=str, default="models/nebula_rag_merged", help="Output merged model path")
    args = parse_args() if "parse_args" in dir() else parser.parse_args()

    print(f"🔄 جاري دمج الموديل {args.base} مع أوزان LoRA من {args.lora}...")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    tokenizer = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    base_model = AutoModelForCausalLM.from_pretrained(
        args.base,
        torch_dtype=torch.float16,
        device_map="cpu",
        trust_remote_code=True,
    )

    merged_model = PeftModel.from_pretrained(base_model, args.lora)
    merged_model = merged_model.merge_and_unload()

    print(f"💾 حفظ الموديل المدمج في {args.out}...")
    merged_model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    print("✅ تم الدمج بنجاح!")


if __name__ == "__main__":
    main()
