# INGRES Gemma Groundwater Fine-Tuning Kit

This folder prepares the two-track Gemma path:

1. Fine-tune a Gemma model with LoRA/QLoRA on INGRES groundwater instruction examples.
2. Deploy the resulting model on a GPU endpoint and let the Render backend call it.

The model should be treated as the language layer. MongoDB, ML models, and the digital twin remain the source of truth.

## 1. Build the dataset

From the repo root:

```powershell
python training/gemma_groundwater/build_dataset.py
```

Output:

```txt
training/gemma_groundwater/data/ingres_gemma_sft.jsonl
```

Each row is chat-style JSONL with system, user, and assistant messages.

## 2. Fine-tune with LoRA

Use a GPU machine. Your Gemma model must be in Hugging Face `transformers` format. If your local download is an Ollama/GGUF model, use it for inference, not LoRA fine-tuning.

```powershell
pip install -r training/gemma_groundwater/requirements.txt
python training/gemma_groundwater/train_lora.py --model C:\path\to\gemma-hf-model
```

For a Hugging Face model id:

```powershell
python training/gemma_groundwater/train_lora.py --model google/gemma-4-<size>-it
```

The adapter is saved to:

```txt
training/gemma_groundwater/out/ingres-gemma-lora
```

## 3. Merge the adapter

```powershell
python training/gemma_groundwater/merge_lora.py --base-model C:\path\to\gemma-hf-model
```

The merged model is saved to:

```txt
training/gemma_groundwater/out/ingres-gemma-merged
```

## 4. Deploy the model

Use a GPU endpoint such as Hugging Face Inference Endpoints, RunPod, Modal, Replicate, or a GPU VM running vLLM/TGI/Ollama.

The Render backend supports these endpoint formats:

```txt
GEMMA_ENDPOINT_FORMAT=openai
GEMMA_ENDPOINT_FORMAT=ollama
GEMMA_ENDPOINT_FORMAT=tgi
```

Recommended production shape:

```txt
Frontend -> Render FastAPI -> Gemma GPU endpoint
```

Render should not run the model locally.

## 5. Render environment variables

Add these to Render after the endpoint is live:

```txt
GEMMA_ENDPOINT_URL=https://your-gemma-endpoint.example/v1/chat/completions
GEMMA_ENDPOINT_FORMAT=openai
GEMMA_MODEL=ingres-gemma
GEMMA_API_KEY=optional_endpoint_secret
GEMMA_TIMEOUT_SECONDS=45
```

If these are missing, INGRES falls back to deterministic rule-based responses or the existing HuggingFace path when `HF_TOKEN` exists.
