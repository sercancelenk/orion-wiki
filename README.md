### OrionWiki

OrionWiki, bir Git reposunu analiz edip **yüksek seviye mimariyi, ana akışları ve önemli bileşenleri** anlatan zengin bir wiki HTML çıktısı üreten, LLM tabanlı hafif bir araçtır.

- **Input**: GitHub / GitLab (on‑prem dahil) repo URL’i + LLM API key’i  
- **Süreç**: Repo klonlama → dosya tarama → chunk’lama → embedding → RAG tabanlı wiki section’ları → tek sayfalık HTML wiki  
- **Output**: Dark tema, sol menülü, Mermaid diyagram destekli tek bir HTML dosyası

Bu repo, `AsyncFuncAI/deepwiki-open` projesinden ilham almış, ancak **stateless / in‑memory MVP** olarak sadeleştirilmiş bir sürümdür.

---

### Özellikler

- **Stateless / in‑memory MVP**
  - Her `Generate Wiki` çağrısı:
    - Repo’yu geçici bir dizine klonlar
    - Embedding + FAISS index’i sadece RAM’de kurar
    - Tüm wiki HTML çıktısını response’ta döner
  - Diskte kalıcı embedding / wiki saklanmaz (runtime cache sadece eski stateful mod için).

- **Mermaid diyagram desteği**
  - `graph TD`, `flowchart`, `sequenceDiagram` blokları otomatik olarak Mermaid’e çevrilir.

- **Private GitLab / GitHub desteği**
  - UI’da `Git Access Token` alanı ile personal access token geçerek private repoları klonlayabilirsin.
  - GitLab için otomatik `https://oauth2:<token>@gitlab.xxx.com/...` formatı kullanılır.

- **Modern dark UI**
  - Sol sidebar: proje logosu (OrionWiki), repo adı, export butonları, sayfa listesi.
  - Sağ ana panel: seçili section içeriği, code block’lar ve diyagramlar.

---

### Gereksinimler

- Python 3.12
- `requirements.txt`’teki bağımlılıklar:
  - `fastapi`, `uvicorn[standard]`, `pydantic`, `requests`
  - `faiss-cpu`, `streamlit`, `openai`, `markdown`
- Git binary (`git clone` için)

LLM sağlayıcısı olarak şu an **OpenAI compatible** endpoint’ler desteklenir (OpenAI, proxied endpoint’ler, OpenRouter vb. base_url ile).

---

### Kurulum (Local)

```bash
git clone https://github.com/<kendi-kullanicin>/orionwiki.git
cd orionwiki

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

#### Backend’i çalıştır

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

#### UI (Streamlit) çalıştır

```bash
streamlit run ui/app.py --server.port 3000 --server.address 0.0.0.0
```

Tarayıcıda `http://localhost:3000` adresine git.

---

### Kullanım

1. **LLM ayarları**
   - Sidebar’dan:
     - `Provider`: `openai`
     - `Chat Model`: varsayılan `gpt-4-turbo` (değiştirilebilir)
     - `Embedding Model`: varsayılan `text-embedding-3-small`
     - `API Key`: OpenAI veya OpenAI‑compatible API anahtarın

2. **Repo URL’i**
   - `GitHub URL` alanına:
     - Ör: `https://github.com/AsyncFuncAI/deepwiki-open`
     - veya on‑prem GitLab:
       - `https://gitlab.xxx.com/group/private-repo`

3. **Private repo’lar için token (opsiyonel)**
   - `Git Access Token` alanına:
     - GitHub PAT
     - veya GitLab personal access token (en az `read_repository` / `api` scope)

4. **Wiki üretimi**
   - `Generate Wiki` butonuna tıkla.
   - Backend:
     - Repo’yu geçici klasöre klonlar
     - In‑memory FAISS index kurar
     - Wiki outline + sayfaları üretir
     - Tam HTML’i geri döner.
   - UI:
     - HTML’i embed eder ve sol menülü wiki arayüzünü gösterir.
     - `Download wiki HTML` butonu ile aynı dosyayı indirebilirsin.

Not: Stateless MVP modunda `Ask this repo` ve Deep Research endpoint’leri UI’dan kaldırılmıştır.

---

### Docker ile Çalıştırma

Repo kökünde bir `Dockerfile` bulunuyor.

```bash
# İmajı build et
docker build -t orionwiki:latest .

# Backend
docker run --rm -p 8001:8001 orionwiki:latest

# UI (ayrı container, aynı imaj)
docker run --rm -p 3000:3000 \
  --env API_BASE="http://host.docker.internal:8001" \
  orionwiki:latest \
  streamlit run ui/app.py --server.port=3000 --server.address=0.0.0.0
```

Linux’ta `host.docker.internal` yerine host IP’sini kullanman gerekebilir.

---

### Kubernetes Deployment

Stateless MVP sürümünü K8s üzerinde koşturmak için ayrıntılı bir rehber `K8S_DEPLOYMENT.md` dosyasında bulunuyor:

- Docker imajı build & push
- Backend Deployment + Service
- UI Deployment + Service (aynı imaj, farklı komut)
- Ingress örneği (`orionwiki.example.com`)
- Private GitLab/GitHub erişimi için notlar

Bkz: `K8S_DEPLOYMENT.md`

---

### Mimarî Notlar ve Gelecek Geliştirmeler

`DEPLOYMENT_NOTES.md` dosyasında:

- Multi‑tenant storage tasarımı (kullanıcı başına namespace)
- Stateful moda geçiş (kalıcı FAISS index + wiki cache)
- Auth / profil / kullanıcı yönetimi (JWT, OAuth, vb.)

için yüksek seviyeli tasarım notları bulunuyor.

Planlanan iyileştirmeler:

- Stateless modun yanında isteğe bağlı **stateful mod** (cache + RAG + Ask this repo).
- Login / profil ve kullanıcı bazlı repo/fiyatlandırma modeli.
- Birden fazla LLM provider desteği (OpenRouter, Gemini, vs.).

---

### Lisans

Bu proje kişisel bir yan proje / eğitim projesi olarak tasarlanmıştır; lisans koşullarını kendi GitHub hesabında belirleyebilirsin (MIT, Apache‑2.0 vb.). README içeriği lisans beyanı içermez. 


