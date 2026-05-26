from pathlib import Path
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification

BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_PATH = BASE_DIR / "models" / "stage2"

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForTokenClassification.from_pretrained(MODEL_PATH)
model.eval()

id2label = model.config.id2label


def predict_stage2(text: str):
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=256,
        return_offsets_mapping=True,
    )

    offsets = inputs.pop("offset_mapping")[0]

    with torch.no_grad():
        outputs = model(**inputs)
        preds = torch.argmax(outputs.logits, dim=2)[0]

    entities = []
    current_entity = None

    for idx, pred_id in enumerate(preds):
        label = id2label[int(pred_id)]
        start, end = offsets[idx].tolist()

        if start == end or label == "O":
            if current_entity:
                entities.append(current_entity)
                current_entity = None
            continue

        word = text[start:end]

        if label.startswith("B-"):
            if current_entity:
                entities.append(current_entity)

            current_entity = {
                "type": label[2:],
                "text": word,
                "start": start,
                "end": end,
            }

        elif label.startswith("I-"):
            entity_type = label[2:]

            if current_entity and current_entity["type"] == entity_type:
                current_entity["text"] += word
                current_entity["end"] = end
            else:
                current_entity = {
                    "type": entity_type,
                    "text": word,
                    "start": start,
                    "end": end,
                }

    if current_entity:
        entities.append(current_entity)

    return entities