import uuid, sqlite3, os
from fastapi import FastAPI, UploadFile, File, HTTPException
from PIL import Image, ImageEnhance
import torch
import torch.nn.functional as F
from transformers import CLIPProcessor, CLIPModel
import io

app = FastAPI(title="PokéDraw Server")

device = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"🧠 Cargando modelo en: {device}")
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
model.eval()

ARTWORK_DIR = "pokemon_artwork_hd"
pokemon_names = sorted([
    os.path.splitext(f)[0] for f in os.listdir(ARTWORK_DIR)
    if f.endswith((".jpg", ".png", ".jpeg"))
])

CACHE_FILE = "pokemon_image_embeddings.pt"

def preprocess_image(img: Image.Image) -> Image.Image:
    # Recortar centro (quita bordes y fondo)
    w, h = img.size
    margin_x, margin_y = int(w * 0.05), int(h * 0.05)
    img = img.crop((margin_x, margin_y, w - margin_x, h - margin_y))
    # Aumentar saturación y contraste para acercar al estilo artwork
    img = ImageEnhance.Color(img).enhance(1.8)
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = ImageEnhance.Sharpness(img).enhance(1.5)
    return img

def compute_image_embedding(img: Image.Image) -> torch.Tensor:
    inputs = processor(images=img, return_tensors="pt").to(device)
    with torch.no_grad():
        emb = model.get_image_features(**inputs)
        if not isinstance(emb, torch.Tensor):
            emb = emb.pooler_output
    return F.normalize(emb, dim=-1).cpu()

# Cargar cache o computar embeddings de los artworks
if os.path.exists(CACHE_FILE):
    print(f"⚡ Cargando embeddings desde cache...")
    cache = torch.load(CACHE_FILE, weights_only=True)
    image_embeddings = cache["embeddings"]
    cached_names = cache["names"]
    # Si cambiaron los pokemones, regenerar
    if cached_names != pokemon_names:
        print("⚠️  Cache desactualizado, regenerando...")
        os.remove(CACHE_FILE)
        image_embeddings = None
    else:
        print(f"✅ Cache cargado: {len(pokemon_names)} pokémones")
else:
    image_embeddings = None

if image_embeddings is None:
    print(f"📦 Indexando {len(pokemon_names)} artworks con CLIP (imagen→imagen)...")
    embeddings_list = []
    for i, name in enumerate(pokemon_names):
        path = os.path.join(ARTWORK_DIR, name + ".jpg")
        if not os.path.exists(path):
            path = os.path.join(ARTWORK_DIR, name + ".png")
        try:
            img = Image.open(path).convert("RGB")
            emb = compute_image_embedding(img)
            embeddings_list.append(emb)
        except Exception as e:
            print(f"  ⚠️  Error con {name}: {e}")
            embeddings_list.append(torch.zeros(1, 512))

        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(pokemon_names)}")

    image_embeddings = torch.cat(embeddings_list, dim=0)  # (N, 512)
    torch.save({"embeddings": image_embeddings, "names": pokemon_names}, CACHE_FILE)
    print(f"✅ Índice de imágenes listo y guardado en cache")

# Embeddings de texto: múltiples prompts por pokémon, promediados
print("📝 Computando embeddings de texto...")
BATCH_SIZE = 64
text_embeddings = []
with torch.no_grad():
    for i in range(0, len(pokemon_names), BATCH_SIZE):
        batch = pokemon_names[i:i+BATCH_SIZE]
        # Varios prompts por pokémon para mayor robustez
        all_prompts = []
        for name in batch:
            all_prompts += [
                f"a drawing of {name}",
                f"a sketch of {name}",
                f"{name} pokemon",
                f"a photo of a {name} pokemon toy",
            ]
        inputs = processor(text=all_prompts, return_tensors="pt", padding=True, truncation=True).to(device)
        emb = model.get_text_features(**inputs)
        if not isinstance(emb, torch.Tensor):
            emb = emb.pooler_output
        emb = F.normalize(emb, dim=-1).cpu()
        # Promediar los 4 prompts por pokémon
        emb = emb.view(len(batch), 4, -1).mean(dim=1)
        emb = F.normalize(emb, dim=-1)
        text_embeddings.append(emb)

text_embeddings = torch.cat(text_embeddings, dim=0)  # (N, 512)
print("✅ Embeddings de texto listos")


def init_db():
    conn = sqlite3.connect("cards.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS pokemon_cards
        (id TEXT PRIMARY KEY, name TEXT, hp INTEGER, attack INTEGER,
         pokemon_score REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()

init_db()


def identify_pokemon(image_bytes: bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = preprocess_image(img)
    img_emb = compute_image_embedding(img)

    # Similitud imagen vs artworks
    sims_img = (img_emb @ image_embeddings.T).squeeze(0)
    # Similitud imagen vs texto
    sims_txt = (img_emb @ text_embeddings.T).squeeze(0)
    # Combinar 60% imagen + 40% texto
    sims = 0.6 * sims_img + 0.4 * sims_txt

    best_idx = sims.argmax().item()
    best_score = sims_img[best_idx].item()  # score real de imagen para stats

    top3_idx = sims.topk(3).indices.tolist()
    top3 = [(pokemon_names[i], round(sims_img[i].item(), 3), round(sims_txt[i].item(), 3)) for i in top3_idx]
    print(f"🎯 Top-3 (img, txt): {top3}")

    matched_name = pokemon_names[best_idx].capitalize()

    hp = int(50 + (best_score * 150) + (hash(image_bytes) % 50))
    attack = int(20 + (best_score * 100) + (sum(image_bytes[:50]) % 40))

    return {
        "name": matched_name,
        "hp": max(10, min(hp, 250)),
        "attack": max(5, min(attack, 200)),
        "pokemon_score": round(best_score, 3),
    }


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(400, "Solo se permiten imágenes")

    img_bytes = await file.read()
    result = identify_pokemon(img_bytes)
    card_id = str(uuid.uuid4())

    conn = sqlite3.connect("cards.db")
    conn.execute(
        "INSERT INTO pokemon_cards (id, name, hp, attack, pokemon_score) VALUES (?,?,?,?,?)",
        (card_id, result["name"], result["hp"], result["attack"], result["pokemon_score"])
    )
    conn.commit()
    conn.close()

    return {"status": "ok", "card_id": card_id, **result}


@app.get("/battle/{player1_id}/{player2_id}")
def battle(player1_id: str, player2_id: str):
    conn = sqlite3.connect("cards.db")
    p1 = conn.execute("SELECT * FROM pokemon_cards WHERE id=?", (player1_id,)).fetchone()
    p2 = conn.execute("SELECT * FROM pokemon_cards WHERE id=?", (player2_id,)).fetchone()
    conn.close()

    if not p1 or not p2:
        raise HTTPException(404, "Carta no encontrada")

    score1 = p1[2] + p1[3]
    score2 = p2[2] + p2[3]
    winner = p1[1] if score1 >= score2 else p2[1]
    return {"winner": winner, "p1_score": score1, "p2_score": score2}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)