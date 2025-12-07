### OrionWiki – Kubernetes Deploy Rehberi (Stateless MVP)

Bu rehber, mevcut stateless / in‑memory OrionWiki sürümünü Kubernetes üzerinde koşturmak için gerekli temel adımları özetler. Bu sürümde:

- FAISS index, repo klonları ve wiki çıktıları kalıcı storage’ta tutulmaz.
- Her `Generate Wiki` isteği baştan analiz yapar, HTML’i üretir ve sadece response’ta döner.
- RAG tabanlı `Ask this repo` ve Deep Research özellikleri devre dışıdır.

---

### 1. Docker imajını inşa et ve registry’ye push et

`Dockerfile` kök dizinde bulunuyor ve hem backend hem UI için ortak base imajı temsil ediyor.

```bash
# 1. İmajı build et
docker build -t <REGISTRY>/<NAMESPACE>/orionwiki:latest .

# 2. Registry'ye push et
docker push <REGISTRY>/<NAMESPACE>/orionwiki:latest
```

Notlar:
- `<REGISTRY>/<NAMESPACE>` kısmını kendi ortamına göre ayarla (örn. `ghcr.io/org`, `registry.gitlab.com/group`, `my-registry.local:5000` vb.).

---

### 2. Kubernetes namespace ve genel değişkenler

İsteğe bağlı olarak ayrı bir namespace kullanabilirsin:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orionwiki
```

```bash
kubectl apply -f namespace.yaml
kubectl config set-context --current --namespace=orionwiki
```

---

### 3. Backend Deployment + Service

Backend, FastAPI + Uvicorn ile 8001 portunda çalışıyor.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orionwiki-backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orionwiki-backend
  template:
    metadata:
      labels:
        app: orionwiki-backend
    spec:
      containers:
        - name: backend
          image: <REGISTRY>/<NAMESPACE>/orionwiki:latest
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8001
          env:
            - name: PORT_BACKEND
              value: "8001"
            # OpenAI / LLM sağlayıcıları için API key'i environment üzerinden de geçirebilirsin,
            # ancak bu projede kullanıcı kendi key'ini UI'dan giriyor; o yüzden burada zorunlu değil.
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
---
apiVersion: v1
kind: Service
metadata:
  name: orionwiki-backend
spec:
  selector:
    app: orionwiki-backend
  ports:
    - name: http
      port: 8001
      targetPort: 8001
  type: ClusterIP
```

Uygula:

```bash
kubectl apply -f orionwiki-backend.yaml
```

---

### 4. UI (Streamlit) Deployment + Service

Aynı imajı kullanarak, komutu override edip Streamlit’i ayağa kaldırıyoruz.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orionwiki-ui
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orionwiki-ui
  template:
    metadata:
      labels:
        app: orionwiki-ui
    spec:
      containers:
        - name: ui
          image: <REGISTRY>/<NAMESPACE>/orionwiki:latest
          imagePullPolicy: IfNotPresent
          command: ["streamlit"]
          args:
            - "run"
            - "ui/app.py"
            - "--server.port=3000"
            - "--server.address=0.0.0.0"
          env:
            - name: API_BASE
              value: "http://orionwiki-backend:8001"
          ports:
            - containerPort: 3000
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
---
apiVersion: v1
kind: Service
metadata:
  name: orionwiki-ui
spec:
  selector:
    app: orionwiki-ui
  ports:
    - name: http
      port: 3000
      targetPort: 3000
  type: ClusterIP
```

Uygula:

```bash
kubectl apply -f orionwiki-ui.yaml
```

Notlar:
- UI pod’u içindeki `API_BASE` env değişkeni, backend service ismine işaret ediyor (`http://orionwiki-backend:8001`), bu sayede cluster içi DNS ile backend’e erişiyor.

---

### 5. Dış dünyaya açmak için Ingress

Cluster’da bir Ingress Controller (NGINX, Traefik vb.) kurulu olduğunu varsayıyoruz.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: orionwiki-ingress
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
spec:
  ingressClassName: nginx  # Kullandığın ingress class'a göre güncelle
  rules:
    - host: orionwiki.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: orionwiki-ui
                port:
                  number: 3000
```

Uygula:

```bash
kubectl apply -f orionwiki-ingress.yaml
```

DNS’te `orionwiki.example.com` adresini Ingress Controller’ın public IP’sine yönlendirdiğinde, UI’ye dışarıdan erişebilirsin.

---

### 6. Private GitLab / GitHub repo erişimi

Bu stateless MVP, private repolar için UI üzerinden **Git Access Token** alıp `git clone` URL’ine enjekte ediyor:

- Kullanıcı UI’de:
  - `GitHub URL` → `https://gitlab.xxx.com/group/private-repo`
  - `Git Access Token` → PAT (örn. GitLab `api` scope’lu token)
- Backend’de:
  - Git URL şu forma dönüştürülüyor:
    - GitLab için: `https://oauth2:<TOKEN>@gitlab.xxx.com/group/private-repo.git`
  - Sadece clone sırasında kullanılıyor, disk’e yazılmıyor.

Kubernetes açısından ekstra gereklilik yok; tek önemli nokta:

- Worker pod’larının network’ten `gitlab.xxx.com`’a erişebiliyor olması (VPC, VPN, firewall kuralları).

---

### 7. Gözlemleme ve loglar

- Backend:
  - Uvicorn + FastAPI logları `stdout`’a yazıyor; `kubectl logs orionwiki-backend-...` ile görebilirsin.
  - Özellikle `/api/generate_ephemeral` endpoint’i için hata durumunda stack trace log’lanıyor.
- UI:
  - Streamlit logları UI pod’unda; HTTP istekleri ve hatalar için `kubectl logs orionwiki-ui-...` kullanabilirsin.

---

### 8. İleride stateful sürüme geçerken

Bu rehber stateless MVP içindir. Sonraki adımlarda:

- FAISS index + wiki çıktıları için PVC veya S3 tarzı storage eklemek,
- `Ask this repo` ve Deep Research endpoint’lerini yeniden aktifleştirmek,
- Auth (login/profile) ve multi‑tenant storage eklemek

için ek Kubernetes objeleri (PersistentVolumeClaim, Secret, ConfigMap, ek Deployments) tasarlamak gerekecektir. Bu değişiklikler yapıldığında bu doküman genişletilebilir.


