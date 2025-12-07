### Production Deployment Notes

Bu dosya, `ai-wiki-builder` projesini production ortama alırken dikkat edilmesi gereken temel mimari kararları özetler.

---

### 1. Multi‑User RAG ve Storage Mimarisi

- **Mevcut durum**
  - `backend/config.py` altında:
    - `STORAGE_DIR / repos` → klonlanan repolar
    - `STORAGE_DIR / faiss` → FAISS index + metadata
    - `STORAGE_DIR / wiki` → üretilmiş markdown ve HTML wiki çıktıları
  - Tüm kullanıcılar tek namespace kullanıyor (`owner_repo`).

- **Multi‑tenant için öneri**
  - **Namespace ekle**:
    - `tenant_id` (veya `user_id`) ile `repo_id` birleştir:
      - Örn: `tenant1_owner_repo`.
    - Dizin yapısını buna göre güncelle:
      - `REPO_DIR / {tenant_id} / {repo_id}`
      - `FAISS_DIR / {tenant_id} / {repo_id}.index`
      - `WIKI_DIR / {tenant_id} / {repo_id}_*.md/html`
  - **Storage’i dışarı taşı**:
    - İlk aşamada: K8s’te `PersistentVolumeClaim` ile shared disk (NFS / managed disk).
    - Orta vadede: `wiki/` ve `faiss/` için S3/GCS gibi object storage kullanmak (özellikle çok sayıda repo için).
  - **Concurrency / locking**
    - Aynı (tenant_id, repo_id) için eşzamanlı `/api/generate` çağrılarını engelle:
      - Basit bir `repo.lock` dosyası
      - veya Redis tabanlı distributed lock.
  - **Temizlik (GC)**
    - “Last accessed” veya “created_at” alanlarına göre:
      - Eski index ve wiki’leri silen periyodik job (cron / K8s CronJob).

---

### 2. Kubernetes Üzerinde Deployment

- **Bileşenler**
  - `backend`:
    - FastAPI + Uvicorn (`backend/main.py`).
    - FAISS, repo klonlama, embedding, LLM entegrasyonu burada.
  - `ui`:
    - Streamlit (`ui/app.py`).
    - Backend ile HTTP üzerinden (`API_BASE`) konuşur.

- **Önerilen K8s nesneleri**
  - Backend:
    - `Deployment` (örn. `replicas: 2–3`).
    - `Service` (ClusterIP).
    - `PersistentVolumeClaim` → `/app/backend/storage` olarak mount.
  - UI:
    - Ayrı `Deployment` + `Service`.
  - Dış erişim:
    - `Ingress` (ör. `wiki-api.example.com` ve `wiki-ui.example.com` hostname’leri).
  - Konfigürasyon:
    - `ConfigMap` → temel ayarlar (ör. API_BASE, CHUNK_SIZE vs. – gerekiyorsa).
    - `Secret` → LLM provider API key’leri (eğer kullanıcı bazlı key yerine merkezi key kullanılırsa).

- **Scaling / iş yükü ayrımı**
  - `/api/generate` ağır bir işlem (repo klonlama + embedding + FAISS index + tüm wiki üretimi).
  - İleride:
    - Bu endpoint’i arka plan job’una taşımak (Celery, RQ, basit bir task queue).
    - Ayrı “worker” Deployment’ları ile scale etmek.
  - `/api/ask` ve `/api/deep_research` görece hafif, fakat LLM çağrıları nedeniyle CPU + network baskısı yaratır:
    - `HorizontalPodAutoscaler` ile backend Deployment’ı CPU/istek sayısına göre ölçeklenebilir.

---

### 3. Kimlik Doğrulama, Kullanıcı Profili ve Yetkilendirme

- **Auth modeli**
  - Basit SaaS senaryosu için:
    - E‑mail + şifre veya
    - OAuth (özellikle GitHub/GitLab login, çünkü kullanıcı zaten repo URL’i veriyor).
  - Backend’de JWT tabanlı auth:
    - `users` tablosu (PostgreSQL vb.): `id, email, hashed_password, created_at, plan, ...`
    - Login endpoint’i token üretir.
    - Protected endpoint’lerde `Depends(get_current_user)` ile kullanıcı doğrulanır.

- **Streamlit entegrasyonu**
  - Login formu Streamlit tarafında.
  - Başarılı login sonrası JWT, `st.session_state["token"]` içinde tutulur.
  - Backend isteklerinde:
    - `Authorization: Bearer <jwt>` header’ı eklenir.

- **Repo ve RAG verisi ile ilişkilendirme**
  - `repos` tablosu:
    - `id, user_id, repo_url, normalized_repo_id, last_generated_at, ...`
  - Storage path’inde `user_id` (veya tenant id) kullanılır:
    - Her kullanıcı kendi namespace’i altında FAISS index + wiki dosyalarına sahip olur.

- **LLM API key yönetimi**
  - Production için iki seçenek:
    1. **Merkezi key**:
       - Backend kendi OpenAI/OpenRouter hesabını kullanır.
       - Kullanıcı başına kota/plan uygulaması backend’de tutulur.
       - Avantaj: Kullanıcı kendi key’ini paylaşmak zorunda kalmaz.
    2. **Kullanıcıya ait key**:
       - Key backend’de (DB’de) encrypt edilmiş halde saklanır.
       - UI, sadece login sonrası “LLM Settings” formu ile bu key’i günceller; request’lerde artık frontenden key gönderilmez.
  - Güvenlik açısından çoğu senaryoda **merkezi key + rate limit / plan** yönetimi önerilir.

---

Bu notlar, projeyi tek kullanıcıdan çok kullanıcıya ölçeklerken ve K8s’e taşırken referans alınacak yüksek seviye mimari kararlardır. İleride ihtiyaç olursa, buradan yola çıkarak detaylı tasarım dokümanları (sequence diagram, component diagram, schema) eklenebilir.


